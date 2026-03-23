#include <stdio.h>
void main(){
	int num,choice;
	
	do{
		printf("당신의 학번을 입력하세요:");
	scanf("%d",&num);
	printf("누구에게 투표하시겠습니까?(1~4번)");
	scanf("%d",&choice);
	switch(choice){
		case 1: printf("%d학번 학생은 1번 후보에게 투표했습니다.\n",num);
		break;
		case 2: printf("%d학번 학생은 2번 후보에게 투표했습니다.\n",num);
		break;
		case 3: printf("%d학번 학생은 3번 후보에게 투표했습니다.\n",num);
		break;
		case 4: printf("%d학번 학생은 4번 후보에게 투표했습니다.\n",num);
		break;
		case 0: printf("후보자 번호로 0을 입력하여 종료합니다!\n");
		break;
		default: printf("후보자 번호를 잘못 입력하셨습니다.\n");
	}}while(choice!=0);
}
